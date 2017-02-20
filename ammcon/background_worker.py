#!/usr/bin/env python3
# Python Standard Library imports
import datetime as dt
import logging
import logging.handlers
import os.path
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


def setup_zmq(frontend_port, backend_port):
    device = ThreadDevice(device_type=zmq.QUEUE, in_type=zmq.ROUTER, out_type=zmq.DEALER)
    device.bind_in("tcp://127.0.0.1:{}".format(frontend_port))
    device.bind_out("tcp://127.0.0.1:{}".format(backend_port))
    # Set high water mark to 1 to set constraint on req/rep pattern
    device.setsockopt_in(zmq.SNDHWM, 1)
    device.setsockopt_out(zmq.RCVHWM, 1)

    # neccesary??
    # device.setsockopt_in(zmq.IDENTITY, b'ROUTER')
    # device.setsockopt_out(zmq.IDENTITY, b'DEALER')

    return device


@click.command()
@click.option('--dev', is_flag=True, help='Enables development mode (simulated serial port)')
def main(dev):
    """Setup and start serial port manager thread."""

    setup_logging()

    # Setup and start ZMQ device thread.
    frontend_port = 5555
    backend_port = 6666
    device = setup_zmq(frontend_port, backend_port)
    device.start()

    logging.info('########### Starting Ammcon serial worker ###########')
    serial_port = SerialManager(SERIAL_PORT) if not dev else VirtualSerialManager(SERIAL_PORT)
    serial_port.start()

    temp_logger = TempLogger(interval=60)
    temp_logger.start()

    temp_logger.join()
    logging.debug('temp logger ended')

    serial_port.join()
    device.join()


if __name__ == '__main__':
    main()

