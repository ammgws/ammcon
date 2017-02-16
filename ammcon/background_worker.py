#!/usr/bin/env python3

# Python Standard Library imports
import datetime as dt
import logging
import logging.handlers
import os.path
from argparse import ArgumentParser
from time import sleep
# Ammcon imports
from ammcon.serialmanager import SerialManager, VirtualSerialManager
from ammcon.templogger import TempLogger
from ammcon.config import LOG_PATH, SERIAL_PORT


def main(arguments):
    """Setup and start serial port manager thread."""

    # Get command line arguments
    parser = ArgumentParser(description='Run Ammcon serial port worker.')
    parser.add_argument('-d', '--dev',
                        dest='dev', action='store_const',
                        const=1, default=0,
                        help='Use virtual serial port for development.')
    args = parser.parse_args(arguments)

    # Configure root logger. Level 5 = verbose to catch mostly everything.
    logger = logging.getLogger()
    logger.setLevel(level=5)

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

    logging.info('########### Starting Ammcon serial worker ###########')
    serial_port = SerialManager(SERIAL_PORT) if not args.dev else VirtualSerialManager(SERIAL_PORT)
    serial_port.start()

    temp_logger = TempLogger(interval=60)
    temp_logger.start()

    while temp_logger.is_alive():
        print('still alive')
        logging.debug('still alive')
        sleep(5)




if __name__ == '__main__':
    from sys import argv
    main(argv[1:])

