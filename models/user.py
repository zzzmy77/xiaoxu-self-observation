"""User model."""
from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db
from utils.timezone import iso_utc


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    settings = db.Column(db.JSON, default=dict, nullable=False)
    profile = db.Column(db.JSON, default=dict, nullable=False)
    cognitive_model = db.Column(db.JSON, default=dict, nullable=False)
    experiments = db.Column(db.JSON, default=dict, nullable=False)

    sessions = db.relationship("Session", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    insights = db.relationship("Insight", backref="user", lazy="dynamic", cascade="all, delete-orphan")

    IDENTITY_OPTIONS = {
        "identity": ["", "职场人", "学生", "创业者", "自由职业者", "斜杠青年", "其他"],
        "status": ["", "工作中", "求职中", "备考中", "创业中", "自由状态", "休假中"],
    }

    @staticmethod
    def default_cognitive_model():
        return {
            "基础信息": {},
            "成长背景": {},
            "人生经历时间线": [],
            "核心关系网络": {},
            "精神发展轨迹": {"core_beliefs": [], "self_awareness_evolution": {}},
            "情绪与心理健康趋势": {},
            "当前生活状态": {},
            "人格行为与认知特征": {"behavioral": [], "cognitive": []},
            "价值观与深层需求": {},
            "兴趣与关注": {},
            "核心模式库": [],
        }

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def get_identity_context(self) -> str:
        """Build a readable identity description from profile fields."""
        p = self.profile or {}
        parts = []
        if p.get("identity"):
            parts.append(p["identity"])
        if p.get("industry"):
            parts.append(f"{p['industry']}行业")
        if p.get("profession"):
            parts.append(p["profession"])
        if p.get("status"):
            parts.append(p["status"])
        return "、".join(parts) if parts else ""

    @classmethod
    def get_or_create_default(cls):
        """Return the default demo user (id=1), creating it if needed.
        Only used by /auth/demo quick-login route.
        """
        user = cls.query.filter_by(username="demo").first()
        if not user:
            from app import db as _db
            user = cls(
                username="demo",
                settings={"mode": "exploring", "notifications": True},
                profile={
                    "identity": "", "status": "",
                    "industry": "", "profession": "",
                    "emotion_frequencies": {},
                    "common_attributions": [],
                    "insight_keywords": [],
                    "total_sessions": 0,
                },
                cognitive_model=cls.default_cognitive_model(),
            )
            user.set_password("demo123")
            _db.session.add(user)
            _db.session.commit()
        return user

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "settings": self.settings,
            "profile": self.profile,
            "cognitive_model": self.cognitive_model,
            "created_at": iso_utc(self.created_at),
        }
