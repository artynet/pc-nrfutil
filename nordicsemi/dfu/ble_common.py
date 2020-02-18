import struct
from uuid import UUID
import logging
from enum import Enum, IntEnum

logger = logging.getLogger(__name__)


class NordicSemiException(Exception):
    pass


class ValidationException(NordicSemiException):
    pass


class NrfDfuOperationError(NordicSemiException):
    pass


class _UUIDWithStrCmp(UUID):
    """ Same as UUID but compares to string (not case sensitive) """

    def __cmp__(self, other):

        if not isinstance(other, UUID):

            if isinstance(other, int):
                return self.int - other

            if isinstance(other, float):
                return self.int - int(other)

            try:
                other = UUID(other)
            except Exception as e:
                logger.warning("{} != {}".format(self, other))
                return -1

        return self.int - other.int

    def __eq__(self, other):
        return self.__cmp__(other) == 0

    def __ne__(self, other):
        return self.__cmp__(other) != 0

    def __gt__(self, other):
        return self.__cmp__(other) > 0

    def __lt__(self, other):
        return self.__cmp__(other) < 0

    def __ge__(self, other):
        return self.__cmp__(other) >= 0

    def __le__(self, other):
        return self.__cmp__(other) <= 0


def _dfu_uuid(n):
    """ NRF DFU UUID """
    base = "8EC9{:04x}-F315-4F60-9FB8-838830DAEA50"
    return _UUIDWithStrCmp(base.format(n))


def _std_uuid(n):
    """ Bluetooth LE "standard" uuid """
    base = "0000{:04x}-0000-1000-8000-00805F9B34FB"
    return _UUIDWithStrCmp(base.format(n))


class BLE_UUID:
    """

    """

    # fmt: off
    S_GENERIC_SERVICE            = _std_uuid(0x1800)
    S_GENERIC_ATTRIBUTE          = _std_uuid(0x1801)
    S_NORDIC_SEMICONDUCTOR_ASA   = _std_uuid(0xFE59)
    S_GENERIC_ATTRIBUTE_PROFILE  = _std_uuid(0x1801)
    # Buttonless characteristics. Buttonless DFU without bonds 	
    C_DFU_BUTTONLESS_UNBONDED    = _dfu_uuid(0x0003)
    # Secure Buttonless DFU characteristic with bond sharing from SDK 14 or newer.
    C_DFU_BUTTONLESS_BONDED      = _dfu_uuid(0x0004)
    # service changed characteristic
    C_SERVICE_CHANGED            = _std_uuid(0x2A05)
    # Commands with OP_CODE. aka CP_UUID 
    C_DFU_CONTROL_POINT          = _dfu_uuid(0x0001)
    # aka DP_UUID 
    C_DFU_PACKET_DATA            = _dfu_uuid(0x0002)
    # fmt: on


class OBJ_TYPE(IntEnum):
    """ 
    object_type.
    enum nrf_dfu_obj_type_t. excl. INVALID  =  0x00 
    """

    # fmt: off
    COMMAND  =  0x01
    DATA     =  0x02
    # fmt: on


class OP_CODE(IntEnum):
    """ 
    operation/command codes to control point characteristic.
    names (more or less) according to C enum nrf_dfu_op_t (OP_CODE) 
    `INVALID =  0xFF` excluded
    """

    # fmt: off
    PROTOCOL_VERSION   =  0x00
    OBJECT_CREATE      =  0x01 # aka CreateObject
    PRN_SET            =  0x02 # aka RECEIPT_NOTIF_SET or setPRN
    CRC_GET            =  0x03 # aka CalcChecSum
    OBJECT_EXECUTE     =  0x04 # aka Execute
    OBJECT_SELECT      =  0x06 # aka ReadObject
    MTU_GET            =  0x07 # aka GetSerialMTU
    OBJECT_WRITE       =  0x08 # aka WriteObject
    PING               =  0x09 # aka Ping
    HARDWARE_VERSION   =  0x0A
    FIRMWARE_VERSION   =  0x0B
    ABORT              =  0x0C
    RESPONSE           =  0x60 # aka Response
    # fmt: on


class RES_CODE(IntEnum):
    """ 
    response codes from control point characteristic.
    note: success is _not_ zero!
    enum nrf_dfu_result_t (RES_CODE).
    excluding INVALID =  0x00
    """

    # fmt: off
    SUCCESS                  =  0x01
    OP_CODE_NOT_SUPPORTED    =  0x02
    INVALID_PARAMETER        =  0x03
    INSUFFICIENT_RESOURCES   =  0x04
    INVALID_OBJECT           =  0x05
    UNSUPPORTED_TYPE         =  0x07
    OPERATION_NOT_PERMITTED  =  0x08
    OPERATION_FAILED         =  0x0A
    EXT_ERROR                =  0x0B # aka ExtendedError
    # fmt: on


class EXT_ERROR(IntEnum):
    """ 
    extended error codes from control point characteristic.
    enum nrf_dfu_ext_error_code_t (NRF_DFU_EXT_ERROR) 
    """

    # fmt: off
    NO_ERROR              =  0x00
    INVALID_ERROR_CODE    =  0x01
    WRONG_COMMAND_FORMAT  =  0x02
    UNKNOWN_COMMAND       =  0x03
    INIT_COMMAND_INVALID  =  0x04
    FW_VERSION_FAILURE    =  0x05
    HW_VERSION_FAILURE    =  0x06
    SD_VERSION_FAILURE    =  0x07
    SIGNATURE_MISSING     =  0x08
    WRONG_HASH_TYPE       =  0x09
    HASH_FAILED           =  0x0A
    WRONG_SIGNATURE_TYPE  =  0x0B
    VERIFICATION_FAILED   =  0x0C
    INSUFFICIENT_SPACE    =  0x0D
    # fmt: on


class FW_TYPE(IntEnum):
    """ enum nrf_dfu_firmware_type_t (NRF_DFU_FIRMWARE_TYPE_) """

    # fmt: off
    SOFTDEVICE   =  0x00
    APPLICATION  =  0x01
    BOOTLOADER   =  0x02
    # fmt: on


def cp_txd_pack(opcode, **kwargs):
    """ pack control point characteristic request/command/transmit data """

    if opcode == OP_CODE.PRN_SET:
        assert len(kwargs) == 1
        prn = kwargs["prn"]  # '<H':uint16 (LE)
        return struct.pack("<BH", opcode, prn)

    if opcode == OP_CODE.OBJECT_SELECT:
        assert len(kwargs) == 1
        obj_type = kwargs["object_type"]  # '<B':uint8
        obj_type = OBJ_TYPE(obj_type)  # raise ValueError if invalid
        return struct.pack("<BB", opcode, obj_type)

    if opcode == OP_CODE.OBJECT_CREATE:
        assert len(kwargs) == 2
        obj_type = kwargs["object_type"]  # B:uint8
        obj_type = OBJ_TYPE(obj_type)  # raise ValueError if invalid
        obj_size = kwargs["size"]  # '<I':uint32 (LE)
        return struct.pack("<BBI", opcode, obj_type, obj_size)

    assert len(kwargs) == 0
    return struct.pack("<B", opcode)


def cp_rxd_unpack(opcode, data, has_header=True):
    """ unpack/parse control point characteristic response/received data """
    if not isinstance(data, (bytes, bytearray)):
        data = bytearray(data)

    if has_header:
        data = cp_rxd_parse_header(opcode, data)

    if opcode == OP_CODE.OBJECT_SELECT:
        (max_size, offset, crc) = struct.unpack("<III", data)  # '<I':uint32 (LE)
        return {"max_size": max_size, "offset": offset, "crc": crc}

    if opcode == OP_CODE.CRC_GET:
        (offset, crc) = struct.unpack("<II", data)  # '<I':uint32 (LE)
        return {"offset": offset, "crc": crc}

    return data


def cp_rxd_parse_header(opcode, data):
    """ parse control point characteristic response/received header and verify success. 
    returns payload with header removed """

    if isinstance(opcode, OP_CODE):
        tx_opcode = opcode
    else:
        tx_opcode = OP_CODE(opcode)

    emsg = "Bad response for {} -".format(tx_opcode)
    if len(data) < 3:
        raise NrfDfuOperationError(
            "{} incomplete response size {}".format(emsg, len(data))
        )

    try:
        rx_opcode = OP_CODE(data[1])
    except ValueError as e:
        raise NrfDfuOperationError("{} {}".format(emsg, e))
    if rx_opcode != tx_opcode:
        raise NrfDfuOperationError(
            "{} unexpected response opcode {}".format(emsg, rx_opcode)
        )

    try:
        rescode = RES_CODE(data[2])
    except ValueError as e:
        raise NrfDfuOperationError("{} {}".format(emsg, e))

    if rescode == RES_CODE.EXT_ERROR:
        if len(data) < 4:
            raise NrfDfuOperationError("{} missing ext_error code".format(emsg))

        try:
            ext_errcode = EXT_ERROR(data[3])
        except ValueError as e:
            raise NrfDfuOperationError("{} {}".format(emsg, e))

        raise NrfDfuOperationError("{} {}".format(emsg, ext_errcode))

    # note SUCCESS is not zero :(
    if rescode != RES_CODE.SUCCESS:
        raise NrfDfuOperationError("{} {}".format(emsg, rescode))

    # success
    return data[3:]

