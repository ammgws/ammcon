# Imports from Python Standard Library
import datetime as dt
import logging
import os.path
from threading import Thread
from time import sleep
# Third party imports
import zmq
from marshmallow import post_dump
from marshmallow_sqlalchemy import ModelSchema
from sqlalchemy import create_engine, Column, ForeignKey, DateTime, Float, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy_utils import database_exists, create_database
# Ammcon imports
import ammcon.h_bytecmds as pcmd
import ammcon.helpers as helpers
from ammcon import LOCAL_PATH

import resource
print('Memory usage: %s (kb)' % resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

# Setup database
# TO DO: restructure code.
database_uri = 'sqlite:///{}'.format(os.path.join(LOCAL_PATH, 'devices_db.sqlite'))
engine = create_engine(database_uri, echo=False)
if not database_exists(engine.url):
    create_database(engine.url)
Base = declarative_base()


class Device(Base):
    """ORM object used to store device data."""
    __tablename__ = 'device'
    __bind_key__ = 'device_logs'

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, nullable=False, unique=True)
    device_desc = Column(String(255), default="Device ID {}".format(device_id), unique=True)

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

# Setup session
# TO DO: restructure code.
Session = sessionmaker()
Session.configure(bind=engine)
# create tables if not already existing
Base.metadata.create_all(engine)


class TempLogger(Thread):
    """Get current temperature and log to database."""

    def __init__(self, interval=60):
        Thread.__init__(self)
        # Disable daemon so that thread isn't killed during a file write
        self.daemon = False
        # Set logging interval (in seconds)
        self.interval = interval
        # Flag used to gracefully exit thread
        self.stop_thread = 0

        # Connect to zeroMQ REQ socket, used to communicate with serial port
        # to do: handle disconnections somehow (though if background serial worker
        # fails then we're screwed anyway)
        context = zmq.Context().instance()
        self.socket = context.socket(zmq.REQ)
        self.socket.connect('tcp://localhost:5555')
        logging.info('############### Connected to zeroMQ server ###############')
        print('Memory usage: %s (kb)' % resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)

    def run(self):
        logging.info('############### Started templogger ###############')
        print('Memory usage: %s (kb)' % resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        while self.stop_thread != 1:
            print('Memory usage: %s (kb)' % resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            # TO DO: support for multiple devices
            logging.debug('116')
            command = pcmd.micro_commands.get('temp', None)

            try:
                logging.debug('120')
                message_tracker = self.socket.send(command, copy=False, track=True)
            except zmq.ZMQError:
                logging.error("ZMQ send failed.")

            logging.debug('Requesting temperature.')
            response = self.socket.recv()  # blocks until response is found
            logging.debug('Response received: %s', helpers.print_bytearray(response))

            # TO DO: fix kludges
            if not response == 'invalid CRC'.encode():
                logging.debug('131')
                temp, humidity = helpers.temp_val(response)

                data_log = Temperature(
                    device_id=1,
                    temperature=temp,
                    humidity=humidity
                )

                session = Session()
                session.add(data_log)
                try:
                    logging.debug('142')
                    session.commit()
                except Exception as err:
                    session.rollback()
                    logging.error('Failed to write to DB, %s.' % err)
                finally:
                    logging.debug('149')
                    session.close()
            else:
                logging.info("Invalid CRC - not logging.")

            # Break logging interval into 1sec sleeps so don't have to wait too long when quitting thread.
            for _ in range(self.interval):
                if self.stop_thread:
                    logging.debug('Templogger thread stop trigger received, breaking out of sleep loop.')
                    break
                sleep(1)

        logging.debug('Templogger thread stop trigger received, stopping while loop.')

    def stop(self):
        self.stop_thread = 1
