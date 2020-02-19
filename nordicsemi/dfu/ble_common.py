import struct
from uuid import UUID
import logging
from enum import Enum, IntEnum

logger = logging.getLogger(__name__)

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
                logger.debug("{} != {}".format(self, other))
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

