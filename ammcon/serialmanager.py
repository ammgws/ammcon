# Python Standard Library imports
import logging
from threading import Thread
from time import sleep
# Third party imports
import serial
import zmq
from crccheck.crc import Crc
# Ammcon imports
import ammcon.h_bytecmds as pcmd
import ammcon.helpers as helpers


class SerialManager(Thread):
    """Class for handling intermediary communication between hardware connected
    to the serial port and Python. By using queues to pass commands to/responses
    from the serial port, it can be shared between multiple Python threads, or
    processes if changed to use multiprocessing module instead.

    TO DO: move to its own module, allow use of zmq/Queue/multiprocessing queue
           or whatever else by abstracting it away
    """

    def __init__(self, port):
        """ Port: Linux using FTDI USB adaptor; '/dev/ttyUSB0' should be OK.
            Linux using rPi GPIO Rx/Tx pins; '/dev/ttyAMA0'
            Windows using USB adaptor or serial port; 'COM1', 'COM2, etc.
        """
        Thread.__init__(self)
        self.daemon = False  # Need thread to block
        self.stop_thread = 0  # Flag used to gracefully exit thread

        # Setup CRC calculator instance. Used to check CRC of response messages
        self.crc_calc = CRC(width=8,
                            poly=pcmd.poly,
                            initvalue=pcmd.init)

        # Setup zeroMQ REP socket for receiving commands
        context = zmq.Context().instance()
        self.socket = context.socket(zmq.REP)
        self.socket.connect("tcp://127.0.0.1:6666")

        self.ser = self.open_serial_port(port)

        # Give microcontroller time to startup (esp. if has bootloader on it)
        sleep(2)

        # Flush input buffer (discard all contents) just in case
        self.ser.reset_input_buffer()

    def run(self):
        # Keep looping, waiting for next request from zeromq client
        while self.stop_thread != 1:
            # Wait for next request from client (on ZMQ socket)
            command = self.socket.recv()
            logging.debug('Received command in queue: %s', command)

            # Send command to microcontroller (over serial port)
            self.send_command(command)

            # sleep(0.3)  # debugging empty response issue. shouldn't need this

            # Read in response from microcontroller
            # raw_response = self.get_response()  # unreliable
            raw_response = self.get_response_until()  # may block forever
            logging.debug('Raw response: %s', helpers.print_bytearray(raw_response))

            # Destuff response
            # Response should be in the following format:
            # [HDR] [ACK] [DESC] [PAYLOAD] [CRC] [END]
            # 1byte 1byte 2bytes <18bytes  1byte 1byte
            #response = self.destuff_bytes(raw_response, method='PPP')
            response = raw_response
            logging.debug('Destuffed   : %s', helpers.print_bytearray(response))

            # Check CRC of destuffed command
            if not self.crc_calc.check_crc(response[4:-1]):
                logging.warning('Invalid CRC received: %s', response[-2:-1])
                response = 'invalid CRC'.encode()

            # Send response back to client
            self.socket.send(response)

    def stop(self):
        self.stop_thread = 1

    @staticmethod
    def open_serial_port(port):
        # Attempt to open serial port.
        try:
            ser = serial.Serial(port=port,
                                baudrate=115200,
                                timeout=2,
                                write_timeout=2)
            # Timeout is set, so reading from serial port may return less
            # characters than requested. With no timeout, it will block until
            # the requested number of bytes are read (eg. ser.read(10)).
            # Note: timeout does not seem to apply to read() (read one byte) or
            #       readline() (read '\n' terminated line). Perhaps need to
            #       implement own timeout in read function...
        except serial.SerialException:
            logging.error('No serial device detected.')
            ser = None
        return ser

    def read_byte(self):
        """
        Read one byte from serial port's receive buffer.
        """
        read_byte = b''
        try:
            read_byte = self.ser.read(size=1)
        except serial.SerialException:
            # Attempted to read from closed port
            logging.error('Serial port not open - unable to read.')
        return read_byte

    def get_response_until(self):
        """
        Read from serial input buffer until end_flag byte is received.
        Note: for some reason pyserial's timeout doesn't work on these read
              commands (tested on Windows and Linux), so this may block forever
              if microcontroller doesn't response for whatever reason.
        """

        # TO DO: rewrite this as it will end prematurely if data byte contains end flag

        recvd_command = b''
        state = "WAIT_HDR"
        while state != "RECV_END":
            in_byte = self.ser.read(size=1)

            if state == "WAIT_HDR":
                if in_byte == pcmd.hdr:
                    recvd_command += in_byte
                    state = "IN_MSG"
            elif state == "IN_MSG":
                if in_byte == pcmd.esc:
                    state = "RECV_ESC"
                elif in_byte == pcmd.end:
                    recvd_command += in_byte
                    state = "RECV_END"
                else:
                    recvd_command += in_byte
            elif state == "RECV_ESC":
                recvd_command += in_byte
                state = "IN_MSG"

        return recvd_command

    def get_response(self):
        """
        Read in microcontroller response from serial input buffer.
        Note: have been having issues with in_waiting either returning 0 bytes
              but still being able to read using something like read(10), or
              in_waiting returning 0 bytes due to returning too fast before
              the microcontroller can respond.
        """

        recvd_command = b''
        # Save value rather than calling in_waiting in the while loop, otherwise
        # will also receive the responses for other commands sent while
        # processing the original command
        bytes_waiting = self.ser.in_waiting
        logging.debug('Bytes in serial input buffer: %s', bytes_waiting)
        while bytes_waiting > 0:
            recvd_command = recvd_command + self.ser.read(size=1)
            bytes_waiting -= 1
        return recvd_command

    def stuff_bytes(self, byte_array, method='COBS'):
        if method == 'COBS':
            return self._stuff_bytes_cobs(byte_array)
        elif method == 'PPP':
            return self._stuff_bytes_ppp(byte_array)
        else:
            raise ValueError("method keyword must be 'PPP' or 'COBS'")

    def destuff_bytes(self, byte_array, method='COBS'):
        if method == 'COBS':
            return self._destuff_bytes_cobs(byte_array)
        elif method == 'PPP':
            return self._destuff_bytes_ppp(byte_array)
        else:
            raise ValueError("method keyword must be 'PPP' or 'COBS'")

    @staticmethod
    def _stuff_bytes_ppp(byte_array):
        """
        Performs PPP-style byte-stuffing on the input byte array.
        Bytes equal to the header, escape or end flag bytes will be escaped.
        """
        stuffed_array = b''

        for b in byte_array:
            hb = bytes([b])
            if hb not in [pcmd.hdr, pcmd.esc, pcmd.end]:
                stuffed_array += hb
            else:
                stuffed_array += pcmd.esc
                stuffed_array += hb

        return stuffed_array

    @staticmethod
    def _destuff_bytes_ppp(byte_array):
        """
        Destuffs a PPP-like byte-stuffed byte array.
        Input byte array is assumed to have the header and end flag bytes still present.
        Returns byte array in the following format:
            [HDR] [ACK] [DESC] [PAYLOAD] [CRC] [END]
            1byte 1byte 2bytes <18bytes  1byte 1byte
        """
        destuffed_array = b''
        state = "WAIT_HDR"
        for b in byte_array:
            hb = bytes([b])

            if state == "WAIT_HDR":
                if hb == pcmd.hdr:
                    destuffed_array += hb
                    state = "IN_MSG"
            elif state == "IN_MSG":
                if hb == pcmd.esc:
                    state = "RECV_ESC"
                elif hb == pcmd.end:
                    destuffed_array += hb
                    state = "WAIT_HDR"
                else:
                    destuffed_array += hb
            elif state == "RECV_ESC":
                destuffed_array += hb
                state = "IN_MSG"

        return destuffed_array

    @staticmethod
    def _stuff_bytes_cobs(byte_array):
        """
        Performs COBS (consistent overhead byte stuffing) on the input byte array.
        """
        stuffed_array = b''

        # TO DO
        pass

    @staticmethod
    def _destuff_bytes_cobs(byte_array):
        """
        Destuffs a COBS stuffed byte array.
        """
        destuffed_array = b''

        # TO DO
        pass

    def send_command(self, command):
        """Send commands to microcontroller via RS232.
        This function deals directly with the serial port.
        """

        # Perform byte stuffing
        command = self.stuff_bytes(command, method='PPP')

        # Calculate CRC for command
        crc = self.crc_calc.calculate_crc(command)

        # Build up command byte array
        command_array = pcmd.hdr + command + crc + pcmd.end

        # Attempt to write to serial port.
        try:
            self.ser.write(command_array)
        except serial.SerialTimeoutException:
            # Write timeout for port exceeded (only if timeout is set).
            logging.error('Serial port timeout exceeded - unable to write.')
        except serial.SerialException:
            # Attempted to write to closed port
            logging.error('Serial port not open - unable to write.')

        # Wait until all data is written
        self.ser.flush()

        logging.info('Command sent to microcontroller: %s', helpers.print_bytearray(command_array))

    def close(self):
        """ Close connection to the serial port."""
        self.ser.close()


class VirtualSerialManager(SerialManager):
    @staticmethod
    def open_serial_port(port):
        return VirtualSerialPort()


class VirtualSerialPort(object):
    def __init__(self):
        self._received = b''
        self.in_waiting = 0

        # TO DO: move CRC stuff to helper function
        # Setup CRC calculator instance. Used to check CRC of response messages
        self.crc_calc = CRC(width=8,
                            poly=pcmd.poly,
                            initvalue=pcmd.init)

    def write(self, data):
        """ Send sample response based on input command.

            Format: [HDR] [ACK] [DESC] [PAYLOAD] [CRC] [END]
                    1byte 1byte 2bytes <18bytes  1byte 1byte
        """
        # Set sample payload for temperature command
        if ord(data[1:2]) in range(ord(b'\xD0'), ord(b'\xDF')):
            ack = pcmd.ack
            #payload = self._generate_temp_payload(temp1=19, temp2=25, humidity=38)
            payload = self._generate_temp_payload()
        # Set sample payload for light command
        elif ord(data[1:2]) in range(ord(b'\xB0'), ord(b'\xBF')):
            ack = pcmd.ack
            payload = self._generate_general_payload(data)
        # Set generic payload for other commands
        else:
            ack = pcmd.nak
            payload = self._generate_general_payload(data)

        # Calculate CRC for command
        crc = self.crc_calc.calculate_crc(payload)

        self._received = pcmd.hdr + ack + self._stuff_bytes_ppp(bytes([data[1]]) + bytes([data[2]]) + payload + crc) + pcmd.end
        logging.debug('Response (virtual): %s', helpers.print_bytearray(self._received))

    def read(self, size):
        if self._received:
            read = self._received[:size]
            self._received = self._received[size:]
        else:
            read = b''
        self.in_waiting = len(read)
        return read

    @staticmethod
    def _generate_temp_payload(temp1=None, temp2=None, humidity=None):
        from random import randrange
        temp1 = temp1 or randrange(1, 38)  # Random temperature value
        temp2 = temp2 or randrange(0, 76, 25)  # Random decimal for temperature: .0, .25, .50 or .75
        humidity = humidity or randrange(10, 80, 5)  # Random humidity value
        return bytes([temp1]) + bytes([temp2]) + bytes([humidity]) + b'\x00'

    @staticmethod
    def _generate_general_payload(data):
        # Payload for light command consists of the inverse of the second byte of DESC
        # To invert the byte, first convert byte string to integer,
        # and then mask it to get the lower 16 bits, then convert back to byte string
        return bytes([~data[2] & 0xFF])

    @staticmethod
    def _stuff_bytes_ppp(byte_array):
        """
        Performs PPP-style byte-stuffing on the input byte array.
        Bytes equal to the header, escape or end flag bytes will be escaped.
        """
        stuffed_array = b''

        for b in byte_array:
            hb = bytes([b])
            if hb not in [pcmd.hdr, pcmd.esc, pcmd.end]:
                stuffed_array += hb
            else:
                stuffed_array += pcmd.esc
                stuffed_array += hb

        return stuffed_array

    def reset_input_buffer(self):
        pass

    def close(self):
        pass

    def flush(self):
        pass


class CRC(object):
    def __init__(self, width, poly, initvalue):
        # Setup CRC calculator instance. Used to check CRC of response messages
        self.crc_calc = Crc(width=width,
                            poly=poly,
                            initvalue=initvalue)

    def calculate_crc(self, byte_array, format_as='bytes'):
        """
        Calculate CRC of byte_array, return as bytes (default) or int.
        TO DO: rename 'format_as' to 'return_as'
        """

        self.crc_calc.reset(value=pcmd.init)
        self.crc_calc.process(byte_array)
        if format_as == 'bytes':
            crc = self.crc_calc.finalbytes()
        elif format_as == 'int':
            crc = self.crc_calc.final()
        else:
            raise ValueError("format_as keyword must be 'bytes' or 'int'")
        return crc

    def check_crc(self, byte_array):
        """
        Check the CRC from the received response with the calculated CRC
        of the payload. If we calculate the CRC of the payload+received CRC
        and it equals 0, then we know that the data is OK (up to whatever %
        the bit error rate is for the CRC algorithm being used).

        True: CRC OK
        False: CRC NG
        """

        crc = self.calculate_crc(byte_array, 'int')
        if crc != 0:
            # Data is invalid/corrupted
            return False
        else:
            return True
