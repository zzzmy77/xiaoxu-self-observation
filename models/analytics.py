"""AnalyticsEvent — internal, for product analysis (not user-facing)."""
from datetime import datetime, timezone
from app import db


class AnalyticsEvent(db.Model):
    __tablename__ = "analytics_events"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=True)
    event_name = db.Column(db.String(64), nullable=False, index=True)
    properties = db.Column(db.JSON, default=dict, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
