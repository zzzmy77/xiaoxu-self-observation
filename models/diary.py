"""Diary model — one entry per conversation."""
from datetime import datetime, date, timezone
from app import db
from utils.timezone import iso_utc, today_bjt


class Diary(db.Model):
    __tablename__ = "diaries"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=True)
    date = db.Column(db.Date, default=lambda: today_bjt(), nullable=False)

    title = db.Column(db.String(200), default="", nullable=False)
    content = db.Column(db.Text, default="", nullable=False)  # HTML content (legacy)

    # Three-part diary structure (v2)
    narrative = db.Column(db.Text, default="", nullable=False)  # 叙事·第一人称
    analysis = db.Column(db.Text, default="", nullable=False)   # 分析·第二人称
    summary = db.Column(db.Text, default="", nullable=False)    # 总结·第一人称

    # Structured data extracted from conversation
    emotion_tags = db.Column(db.JSON, default=list, nullable=False)
    key_events = db.Column(db.JSON, default=list, nullable=False)
    user_reflections = db.Column(db.JSON, default=list, nullable=False)

    insight_ref = db.Column(db.Integer, db.ForeignKey("insights.id"), nullable=True)
    is_edited = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "date": self.date.isoformat() if self.date else None,
            "title": self.title,
            "content": self.content,
            "narrative": self.narrative,
            "analysis": self.analysis,
            "summary": self.summary,
            "emotion_tags": self.emotion_tags,
            "key_events": self.key_events,
            "user_reflections": self.user_reflections,
            "insight_ref": self.insight_ref,
            "is_edited": self.is_edited,
            "created_at": iso_utc(self.created_at),
            "updated_at": iso_utc(self.updated_at),
        }
