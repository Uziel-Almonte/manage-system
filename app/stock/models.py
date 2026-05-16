from app.database import db
from datetime import datetime

class StockMovement(db.Model):
    __tablename__ = 'stock_movements'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    user = db.Column(db.String(100), nullable=True) 
    type = db.Column(db.String(50), nullable=False) 
    prev_qty = db.Column(db.Integer, nullable=False)
    new_qty = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    date = db.Column(db.DateTime, default=db.func.now(), nullable=False)

    product = db.relationship('Product', backref='movements')

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'user': getattr(self, 'user', None),
            'type': self.type,
            'prev_qty': self.prev_qty,
            'new_qty': self.new_qty,
            'notes': self.notes,
            'date': self.date.isoformat() if self.date else None
        }
