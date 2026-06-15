"""MonthlySummary — one summary per 30-day period from user's first activity."""
from datetime import datetime, date, timedelta, timezone
from app import db
from utils.timezone import iso_utc, today_bjt


class MonthlySummary(db.Model):
    __tablename__ = "monthly_summaries"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    period = db.Column(db.Integer, nullable=False)  # 1-based: 1st 30 days, 2nd 30 days...
    period_start = db.Column(db.Date, nullable=False)

    # LLM-generated
    title = db.Column(db.String(200), default="", nullable=False)
    summary_text = db.Column(db.Text, default="", nullable=False)
    key_discoveries = db.Column(db.JSON, default=list, nullable=False)
    growth_timeline = db.Column(db.JSON, default=list, nullable=False)

    # Aggregated data
    emotion_frequencies = db.Column(db.JSON, default=dict, nullable=False)
    attribution_distribution = db.Column(db.JSON, default=dict, nullable=False)
    diary_count = db.Column(db.Integer, default=0)
    insight_count = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    @property
    def period_end(self):
        """Return the exclusive end date (start + 30 days)."""
        return self.period_start + timedelta(days=30)

    @property
    def label(self):
        start = self.period_start
        end = self.period_end - timedelta(days=1)
        return f"第{self.period}期 ({start.month}/{start.day} - {end.month}/{end.day})"

    @classmethod
    def get_period_for_date(cls, first_activity_date: date, target_date: date) -> int:
        """Calculate which 30-day period a date falls into."""
        delta = (target_date - first_activity_date).days
        return max(1, delta // 30 + 1)

    @classmethod
    def get_period_range(cls, first_activity_date: date, period_num: int):
        """Return (start_date, end_date_exclusive) for a given period number."""
        start = first_activity_date + timedelta(days=(period_num - 1) * 30)
        end = start + timedelta(days=30)
        return start, end

    @classmethod
    def get_first_activity_date(cls, user_id: int) -> date | None:
        """Find the user's earliest diary or message date."""
        from models.diary import Diary
        from models.message import Message
        from models.session import Session

        earliest = None
        first_diary = Diary.query.filter_by(user_id=user_id).order_by(Diary.date.asc()).first()
        if first_diary:
            earliest = first_diary.date

        first_session = (Session.query
                         .filter_by(user_id=user_id)
                         .order_by(Session.created_at.asc())
                         .first())
        if first_session and first_session.created_at:
            sess_date = first_session.created_at.date()
            if earliest is None or sess_date < earliest:
                earliest = sess_date

        return earliest or today_bjt()

    def to_dict(self):
        return {
            "id": self.id,
            "period": self.period,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "label": self.label,
            "title": self.title,
            "summary_text": self.summary_text,
            "key_discoveries": self.key_discoveries,
            "growth_timeline": self.growth_timeline,
            "emotion_frequencies": self.emotion_frequencies,
            "attribution_distribution": self.attribution_distribution,
            "diary_count": self.diary_count,
            "insight_count": self.insight_count,
            "created_at": iso_utc(self.created_at),
        }
