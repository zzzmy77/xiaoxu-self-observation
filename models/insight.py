"""Insight model."""
from datetime import datetime, timezone
from app import db
from utils.timezone import iso_utc


class Insight(db.Model):
    __tablename__ = "insights"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    emotion_tags = db.Column(db.JSON, default=list, nullable=False)
    attribution_chain = db.Column(db.JSON, default=list, nullable=False)
    insight_text = db.Column(db.Text, default="", nullable=False)
    pattern_ref = db.Column(db.JSON, default=dict, nullable=False)
    pattern_hint = db.Column(db.String(200), default="", nullable=False)
    occurrence_count = db.Column(db.Integer, default=1, nullable=False)
    last_occurrence = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    evolution_stages = db.Column(db.JSON, default=list, nullable=False)
    hypotheses = db.Column(db.JSON, default=list, nullable=False)
    triggers = db.Column(db.JSON, default=list, nullable=False)
    affected_areas = db.Column(db.JSON, default=list, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "emotion_tags": self.emotion_tags,
            "attribution_chain": self.attribution_chain,
            "insight_text": self.insight_text,
            "pattern_ref": self.pattern_ref,
            "pattern_hint": self.pattern_hint,
            "occurrence_count": self.occurrence_count,
            "last_occurrence": iso_utc(self.last_occurrence),
            "evolution_stages": self.evolution_stages,
            "hypotheses": self.hypotheses,
            "triggers": self.triggers,
            "affected_areas": self.affected_areas,
            "created_at": iso_utc(self.created_at),
        }
