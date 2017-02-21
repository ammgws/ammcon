# Imports from Python Standard Library
import logging
from threading import Thread
from time import sleep
# Third party imports
import zmq
# Ammcon imports
import ammcon.h_bytecmds as pcmd
import ammcon.helpers as helpers
from ammcon import Session
from ammcon.models import Temperature


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
        self.socket.connect('tcp://127.0.0.1:5555')
        logging.info('############### Connected to zeroMQ server ###############')

    def run(self):
        logging.info('############### Started templogger ###############')
        while self.stop_thread != 1:
            # TO DO: support for multiple devices
            command = pcmd.micro_commands.get('temp', None)

            try:
                # TO DO: use ZMQ message tracker?
                message_tracker = self.socket.send(command, copy=False, track=True)
            except zmq.ZMQError:
                logging.error("ZMQ send failed.")

            logging.debug('Requesting temperature.')
            response = self.socket.recv()  # blocks until response is found
            logging.debug('Response received: %s', helpers.print_bytearray(response))

            # TO DO: fix kludges
            if not response == 'invalid CRC'.encode():
                try:
                    temp, humidity = helpers.temp_val(response)
                except Exception as e:
                    # TO DO: fix this kludge
                    # templogger gets non-temp response back from microcontroller
                    # ZMQ is on a strict recv/send pattern so it's highly unlikely to be ZMQ messing up destinations
                    # possibly to do with microcontroller or the serial buffer?
                    logging.debug('fack %s' % e)
                    temp = None
                    humidity = None

                if temp is not None:
                    data_log = Temperature(
                        device_id=1,
                        temperature=temp,
                        humidity=humidity
                    )

                    session = Session()
                    session.add(data_log)
                    try:
                        session.commit()
                    except Exception as err:
                        session.rollback()
                        logging.error('Failed to write to DB, %s.' % err)
                    finally:
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
