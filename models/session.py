"""Session model."""
from datetime import datetime, timezone
from app import db
from utils.timezone import iso_utc


class Session(db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    mode = db.Column(db.String(20), default="exploring")  # exploring | listening
    summary = db.Column(db.JSON, default=dict, nullable=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    messages = db.relationship(
        "Message", backref="session", lazy="dynamic",
        cascade="all, delete-orphan", order_by="Message.created_at"
    )

    def add_message(self, role, content, structured_meta=None):
        from models.message import Message
        msg = Message(
            session_id=self.id,
            role=role,
            content=content,
            structured_meta=structured_meta or {},
        )
        db.session.add(msg)
        db.session.commit()
        return msg

    def get_history(self, limit=30, reverse=False):
        """Return messages as a list of dicts.

        Args:
            limit: max messages to return (None = no limit)
            reverse: if True, return the most recent `limit` messages
                     (does a DESC query then reverses the list)
        """
        from models.message import Message
        query = self.messages.order_by(
            Message.created_at.desc() if reverse else Message.created_at.asc()
        )
        if limit is not None:
            query = query.limit(limit)
        msgs = query.all()
        result = [{"role": m.role, "content": m.content, "created_at": iso_utc(m.created_at)} for m in msgs]
        if reverse:
            result.reverse()
        return result

    def get_all_messages(self):
        from models.message import Message
        return self.messages.order_by(Message.created_at.asc()).all()

    def to_dict(self, include_messages=False):
        d = {
            "id": self.id,
            "mode": self.mode,
            "active": self.active,
            "summary": self.summary,
            "created_at": iso_utc(self.created_at),
        }
        if include_messages:
            d["messages"] = [m.to_dict() for m in self.get_all_messages()]
        return d
