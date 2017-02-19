#!/usr/bin/env python3

# Python Standard Library imports
import datetime as dt
import logging
import logging.handlers
import os.path
from time import sleep
# Third party imports
import click
import zmq
from zmq.devices import ThreadDevice
# Ammcon imports
from ammcon.serialmanager import SerialManager, VirtualSerialManager
from ammcon.templogger import TempLogger
from ammcon.config import LOG_PATH, SERIAL_PORT


def setup_logging(log_level=logging.DEBUG):
    # Configure root logger.
    logger = logging.getLogger()
    logger.setLevel(level=log_level)

    if not os.path.exists(LOG_PATH):
        os.makedirs(LOG_PATH, exist_ok=True)
    log_filename = 'ammcon_serial_{0}.log'.format(dt.datetime.now().strftime("%Y%m%d_%Hh%Mm%Ss"))
    log_fullpath = os.path.join(LOG_PATH, log_filename)
    print('Logging to {}'.format(log_fullpath))
    log_handler = logging.handlers.RotatingFileHandler(log_fullpath,
                                                       maxBytes=5242880,
                                                       backupCount=3)
    log_format = logging.Formatter(
        fmt='%(asctime)s %(name)-12s %(levelname)-8s %(message)s (%(filename)s:%(lineno)d)',
        datefmt=None)
    log_handler.setFormatter(log_format)
    logger.addHandler(log_handler)


@click.command()
@click.option('--dev', is_flag=True, help='Enables development mode (simulated serial port)')
def main(dev):
    """Setup and start serial port manager thread."""

    setup_logging()

    device = ThreadDevice(zmq.QUEUE, zmq.ROUTER, zmq.DEALER)
    device.bind_in('tcp://*:5555')
    device.connect_out('tcp://127.0.0.1:12543')
    device.setsockopt_in(zmq.IDENTITY, 'ROUTER')
    device.setsockopt_out(zmq.IDENTITY, 'DEALER')
    device.start()

    logging.info('########### Starting Ammcon serial worker ###########')
    serial_port = SerialManager(SERIAL_PORT) if not dev else VirtualSerialManager(SERIAL_PORT)
    serial_port.start()

    temp_logger = TempLogger(interval=60)
    temp_logger.start()

    temp_logger.join()
    print('temp logger ended')
    logging.debug('temp logger ended')

    serial_port.join()


if __name__ == '__main__':
    main()

