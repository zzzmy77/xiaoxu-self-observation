"""Initialize Flask app and extensions."""
import os
import logging
from datetime import date, datetime, timezone, timedelta

from flask import Flask

# ── Logging configuration ──
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
log_file = os.getenv("LOG_FILE", "")
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    filename=log_file or None,
    encoding="utf-8",
)
if not log_file:
    # Also output to console if no log file
    console = logging.StreamHandler()
    console.setLevel(getattr(logging, log_level, logging.INFO))
    console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger("").addHandler(console)

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from apscheduler.schedulers.background import BackgroundScheduler

from config import Config

logger = logging.getLogger(__name__)

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    # Enable WAL mode for SQLite to handle concurrent reads
    if "sqlite" in Config.SQLALCHEMY_DATABASE_URI:
        from sqlalchemy import event
        from sqlalchemy.engine import Engine
        @event.listens_for(Engine, "connect")
        def _set_sqlite_wal(dbapi_connection, connection_record):
            dbapi_connection.execute("PRAGMA journal_mode=WAL")
            dbapi_connection.execute("PRAGMA synchronous=NORMAL")

    # Initialize Flask-Migrate with migrations directory
    import os as _os
    _migrate_dir = _os.path.join(_os.path.dirname(__file__), "migrations")
    migrate.init_app(app, db, directory=_migrate_dir)
    if not _os.path.exists(_migrate_dir):
        logger.info("Migrations directory not found. Auto-creating with 'flask db init'...")

    login_manager.init_app(app)

    with app.app_context():
        from models import (  # noqa: F401
            User, Session, Message, Insight,
            Diary, MonthlySummary, AnalyticsEvent,
        )
        db.create_all()

    # Pre-warm vector store synchronously (blocking, not daemon thread)
    # Ensures KnowledgeStore is ready before any request needs L3 search
    if os.getenv("DISABLE_VECTOR", "").lower() not in ("1", "true"):
        try:
            from agents.knowledge_store import init_vector_store
            init_vector_store()
            logger.info("Vector store initialized")
        except Exception as e:
            logger.warning("Vector store init skipped: %s", e)

    # Flask-Login loader
    @login_manager.user_loader
    def load_user(user_id):
        from models.user import User
        return User.query.get(int(user_id))

    from routes.auth import auth_bp
    from routes.chat import chat_bp
    from routes.insights import insights_bp
    from routes.profile import profile_bp
    from routes.diaries import diaries_bp
    from routes.monthly import monthly_bp
    from routes.admin import admin_bp
    from routes.analytics import analytics_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(insights_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(diaries_bp)
    app.register_blueprint(monthly_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(analytics_bp)

    # ── Health check ──
    @app.route("/health")
    def health():
        return {"status": "ok", "app": "小绪·自我观察日记"}

    @app.route("/")
    def index():
        from flask_login import current_user
        if current_user.is_authenticated:
            from flask import redirect, url_for
            return redirect(url_for("chat.index"))
        from flask import redirect, url_for
        return redirect(url_for("auth.login"))

    # ── Manual trigger route for testing ──
    @app.route("/admin/trigger-diary")
    def trigger_diary():
        from flask_login import current_user
        if not current_user.is_authenticated:
            from flask import redirect, url_for
            return redirect(url_for("auth.login"))
        with app.app_context():
            _run_daily_diaries()
        return "Diary generation triggered. Check logs."

    # ── Start scheduler ──
    _start_scheduler(app)

    return app


def _run_daily_diaries():
    """Generate diaries for all users with conversations from yesterday (Beijing time)."""
    from models.user import User
    from agents.diary_agent import DiaryAgent

    bj_now = datetime.now(timezone.utc) + timedelta(hours=8)
    yesterday_bj = bj_now.date() - timedelta(days=1)

    agent = DiaryAgent()
    users = User.query.all()
    count = 0
    for user in users:
        try:
            diary = agent.generate_daily(user, yesterday_bj)
            if diary:
                count += 1
        except Exception as e:
            logger.error("Daily diary error for user %d: %s", user.id, e)

    logger.info("Daily diary generation complete: %d diaries for %s", count, yesterday_bj)

    # Also check and generate monthly summaries that need updating
    _run_monthly_summaries()


def _run_monthly_summaries():
    """Check if any user has a completed 30-day period ready for a summary."""
    from models.user import User
    from models.monthly_summary import MonthlySummary
    from agents.monthly_summary_agent import MonthlySummaryAgent

    bj_now = datetime.now(timezone.utc) + timedelta(hours=8)
    today_bj = bj_now.date()

    agent = MonthlySummaryAgent()
    users = User.query.all()
    generated = 0
    for user in users:
        first_date = MonthlySummary.get_first_activity_date(user.id)
        current_period = MonthlySummary.get_period_for_date(first_date, today_bj)
        # Check if current period has enough data (at least 3 diaries or 2 insights)
        # and generate if not already done
        for p in range(1, current_period + 1):
            existing = MonthlySummary.query.filter_by(
                user_id=user.id, period=p
            ).first()
            if existing and existing.diary_count >= 0:
                continue  # Already generated
            try:
                summary = agent.generate(user, p)
                if summary and summary.diary_count > 0:
                    generated += 1
            except Exception as e:
                logger.error("Monthly summary error for user %d period %d: %s",
                             user.id, p, e)

    if generated:
        logger.info("Monthly summaries auto-generated: %d new", generated)


def _start_scheduler(app):
    """Start APScheduler for daily diary generation at 2:00 AM Asia/Shanghai."""
    if os.getenv("DISABLE_SCHEDULER", "").lower() in ("1", "true"):
        logger.info("Scheduler disabled via DISABLE_SCHEDULER")
        return

    scheduler = BackgroundScheduler()

    def job():
        with app.app_context():
            _run_daily_diaries()

    scheduler.add_job(
        job,
        trigger="cron",
        hour=2,
        minute=0,
        timezone="Asia/Shanghai",
        id="daily_diary",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("APScheduler started: daily diary at 02:00 Asia/Shanghai")


if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)


# Lazy application for production (resolves on first request, not at import time)
#   waitress-serve --port=$PORT app:application
class _LazyWSGI:
    _app = None
    def __call__(self, environ, start_response):
        if _LazyWSGI._app is None:
            _LazyWSGI._app = create_app().wsgi_app
        return _LazyWSGI._app(environ, start_response)

application = _LazyWSGI()
