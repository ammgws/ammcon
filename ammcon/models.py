# Imports from Python Standard Library
import datetime as dt
# Third party imports
from marshmallow import post_dump
from marshmallow_sqlalchemy import ModelSchema
from sqlalchemy import Column, ForeignKey, DateTime, Float, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Device(Base):
    """ORM object used to store device data."""
    __tablename__ = 'device'
    __bind_key__ = 'device_logs'

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, nullable=False, unique=True)
    device_desc = Column(String(255), default="Device {}".format(device_id), unique=True)

    # Define relationships
    device_data = relationship('Temperature', back_populates='device')

    def __repr__(self):
        return '<Device %r>' % self.device_desc


class Temperature(Base):
    """ORM object used to store temperature data."""
    __tablename__ = 'temperature'
    __bind_key__ = 'device_logs'

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey('device.id'))  # __tablename__ is 'device', column is 'id'
    temperature = Column(Float)
    humidity = Column(Float)
    datetime = Column(DateTime(timezone=True), default=dt.datetime.utcnow)  # store as UTC time

    # Define relationships
    device = relationship('Device', back_populates='device_data')

    def __repr__(self):
        return "<DeviceInfo(temperature='%s', humidity='%s')>" % (self.temperature, self.humidity)


class DeviceSchema(ModelSchema):
    """Marshmallow schema used to deserialise Device ORM."""
    class Meta:
        model = Device


class TemperatureSchema(ModelSchema):
    """Marshmallow schema used to deserialise Temperature ORM."""
    class Meta:
        model = Temperature
        dateformat = 'iso'

    @post_dump(pass_many=True)
    def wrap_json_array(self, data, many=False):
        """ Ensure protection against JSON array vulnerabilites that exist in older browsers by wrapping arrays with
            a top level object. Non array JSON (when many=False) are OK as-is.
        """
        if many:
            return {'data': data}
        return data
