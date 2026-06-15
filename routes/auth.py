"""Auth routes — login, register, logout, demo quick-login."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from app import db
from models.user import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("chat.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("chat.index"))

        flash("用户名或密码错误", "error")

    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("chat.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        identity = request.form.get("identity", "")
        status = request.form.get("status", "")
        industry = request.form.get("industry", "")
        profession = request.form.get("profession", "")

        # Validation
        errors = []
        if not username or len(username) < 2:
            errors.append("用户名至少2个字符")
        if not password or len(password) < 6:
            errors.append("密码至少6位")
        if User.query.filter_by(username=username).first():
            errors.append("用户名已被使用")

        if errors:
            for err in errors:
                flash(err, "error")
            return render_template("register.html", form_data=request.form, identity_options=User.IDENTITY_OPTIONS)

        # Create user
        user = User(
            username=username,
            settings={"mode": "exploring", "notifications": True},
            profile={
                "identity": identity,
                "status": status,
                "industry": industry,
                "profession": profession,
                "emotion_frequencies": {},
                "common_attributions": [],
                "insight_keywords": [],
                "total_sessions": 0,
            },
            cognitive_model=User.default_cognitive_model(),
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        # Auto-login after registration
        login_user(user)
        flash("注册成功，欢迎使用小绪！", "success")
        return redirect(url_for("chat.index"))

    return render_template("register.html", identity_options=User.IDENTITY_OPTIONS)


@auth_bp.route("/demo")
def demo_login():
    """Quick one-click demo login."""
    user = User.query.filter_by(username="demo").first()
    if not user:
        user = User.get_or_create_default()
    # Ensure cognitive_model is initialized
    if not user.cognitive_model or not isinstance(user.cognitive_model, dict) or not user.cognitive_model.get("精神发展轨迹"):
        user.cognitive_model = User.default_cognitive_model()
        db.session.commit()
    login_user(user)
    if not user.experiments:
        user.experiments = assign_experiments(user)
        db.session.commit()
    return redirect(url_for("chat.index"))


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
