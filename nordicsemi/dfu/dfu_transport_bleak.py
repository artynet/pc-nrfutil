from os.path import join as path_join
import asyncio
import logging
import time
from shutil import rmtree
from tempfile import mkdtemp
from binascii import crc32

# Nordic libraries
from nordicsemi.dfu.package import Package

# TODO no wild card imports
from nordicsemi.dfu.ble_common import BLE_UUID
from nordicsemi.dfu.operation import OP_CODE, RES_CODE, OBJ_TYPE, op_txd_pack, op_rxd_unpack

from bleak import BleakClient, discover
from bleak.exc import BleakError

logger = logging.getLogger(__name__)


class _ATimeoutEvent(asyncio.Event):
    """ 
    Same as asyncio.Event but wait has a timeout option like threading.Event 
    """

    async def wait(self, timeout=None):
        """ return True on success, False on timeout """
        if timeout is None:
            await super().wait()
            return True

        try:
            await asyncio.wait_for(super().wait(), timeout)
        except asyncio.TimeoutError:
            return False

        return True


class _ATimeoutQueue(asyncio.Queue):
    """ 
    Same as asyncio.Queue but get has a timeout option like queue.Queue 
    but raises asyncio.TimeoutError and not queue.Empty Exception.
    """

    async def get(self, timeout=None):
        """ on timeout raises asyncio.TimeoutError not queue.Empty """
        if timeout is None:
            return await super().get()
        else:
            return await asyncio.wait_for(super().get(), timeout)



class DfuImage:
    """ Paths to a binary(firmware) file with init_packet """
    def __init__(self, unpacked_zip, firmware):
        self.init_packet = path_join(unpacked_zip, firmware.dat_file)
        self.bin_file = path_join(unpacked_zip, firmware.bin_file)

class DfuImagePkg:
    # TODO this class not needed!? either add this to class Manifest 
    # or extend it like `ManifestWithPaths(Manifest)`
    """ Class to abstract the DFU zip Package structure and only expose
    init_packet and binary file paths. """


    def __init__(self, zip_file_path):
        """
        @param zip_file_path: Path to the zip file with the firmware to upgrade
        """
        self.temp_dir     = mkdtemp(prefix="nrf_dfu_")
        self.unpacked_zip = path_join(self.temp_dir, 'unpacked_zip')
        self.manifest     = Package.unpack_package(zip_file_path, self.unpacked_zip)

        self.images = {}

        if self.manifest.softdevice_bootloader:
            k = "softdevice_bootloader"
            self.images[k] = DfuImage(self.unpacked_zip, self.manifest.softdevice_bootloader)

        if self.manifest.softdevice:
            k = "softdevice"
            self.images[k] = DfuImage(self.unpacked_zip, self.manifest.softdevice)

        if self.manifest.bootloader:
            k = "bootloader"
            self.images[k] = DfuImage(self.unpacked_zip, self.manifest.bootloader)

        if self.manifest.application:
            k = "application"
            self.images[k] = DfuImage(self.unpacked_zip, self.manifest.application)

    def __del__(self):
        """
        Destructor removes the temporary directory for the unpacked zip
        :return:
        """
        rmtree(self.temp_dir)

    def get_total_size(self):
        total_size = 0
        for name, image in self.images.items():
            total_size += os.path.getsize(image.bin_file)
        return total_size




class DfuDevice:
    """
    class represents a device already in DFU
    """

    def __init__(self, *args, **kwargs):
        self.address = kwargs.get("address")
        if self.address is None:
            raise ValueError("invalid address")

        timeout = kwargs.get("timeout", 10)
        self._bleclnt = BleakClient(self.address, timeout=timeout)

        # TODO what packet_size? 20 seems small --> slow
        # packet size ATT_MTU_DEFAULT - 3
        # ATT_MTU_DEFAULT = driver.GATT_MTU_SIZE_DEFAULT
        # #define GATT_MTU_SIZE_DEFAULT 23
        self.packet_size = 20

        self._evt_opcmd = _ATimeoutEvent()
        self.prn = 0
        self.RETRIES_NUMBER = 3

    async def __aenter__(self):
        logger.debug("{} - connecting...".format(self.address))
        await self._bleclnt.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        logger.debug("{} - disconnecting...".format(self.address))
        await self._bleclnt.disconnect()

    async def cp_cmd(self, opcode, **kwargs):
        """ 
        control point (cp) characteristic command - handles request, 
        parses response and chech success.
        returns payload (if any)
        """
        cpuuid = BLE_UUID.C_DFU_CONTROL_POINT
        txdata = op_txd_pack(opcode, **kwargs)
        if not isinstance(txdata, bytearray):
            # bytes object not supported in txdbus
            txdata = bytearray(txdata)

        self._evt_opcmd.clear()

        rxdata = bytearray()

        def response_handler(sender, data):
            # sender is str. should be uuid!?
            if sender != cpuuid:
                logger.warning(
                    "unexpected notify response \
                        from {} expected {}".format(
                        sender, cpuuid
                    )
                )
                return
            rxdata.extend(data)
            logger.debug("cp_cmd RXD:{}".format(data))
            self._evt_opcmd.set()

        await self._bleclnt.start_notify(cpuuid, response_handler)
        await self._bleclnt.write_gatt_char(cpuuid, txdata, response=True)

        if not await self._evt_opcmd.wait(6):
            raise NrfDfuOperationError(
                "CP Operation response timeout {}".format(opcode)
            )

        return op_rxd_unpack(opcode, rxdata)

    async def dpkg_write(self, data):
        await self._bleclnt.write_gatt_char(
            BLE_UUID.C_DFU_PACKET_DATA, data, response=True
        )

    async def _validate_crc(self, crc, offset):
        response = await self.cp_cmd(OP_CODE.CRC_GET)
        if crc != response["crc"]:
            raise ValidationException(
                "Failed CRC validation.\n"
                + "Expected: {} Received: {}.".format(crc, response["crc"])
            )
        if offset != response["offset"]:
            raise ValidationException(
                "Failed offset validation.\n"
                + "Expected: {} Received: {}.".format(offset, response["offset"])
            )

    async def __stream_data(self, data, crc=0, offset=0):
        """ write to package data characteristic (aka DP_UUID or data_point) in
        chunks and verify success"""
        logger.debug(
            "BLE: Streaming Data: len:{0} offset:{1} crc:0x{2:08X}".format(
                len(data), offset, crc
            )
        )

        current_pnr = 0
        for i in range(0, len(data), self.packet_size):
            packet = data[i : i + self.packet_size]
            # was: self.write_data_point(packet)
            await self._bleclnt.write_gatt_char(
                BLE_UUID.C_DFU_PACKET_DATA, packet, response=True
            )
            crc = crc32(packet, crc) & 0xFFFFFFFF
            offset += len(packet)
            current_pnr += 1
            if self.prn == current_pnr:
                current_pnr = 0
                await self._validate_crc(crc, offset)

        await self._validate_crc(crc, offset)

        return crc

    async def send_init_packet(self, init_packet):
        async def try_to_recover():
            if response["offset"] == 0 or response["offset"] > len(init_packet):
                # There is no init packet or present init packet is too long.
                return False

            expected_crc = (
                crc32(init_packet[: response["offset"]]) & 0xFFFFFFFF
            )

            if expected_crc != response["crc"]:
                # Present init packet is invalid.
                return False

            if len(init_packet) > response["offset"]:
                # Send missing part.
                try:
                    await self.__stream_data(
                        data=init_packet[response["offset"] :],
                        crc=expected_crc,
                        offset=response["offset"],
                    )
                except ValidationException:
                    return False

            # was: self.__execute()
            await self.cp_cmd(OP_CODE.OBJECT_EXECUTE)
            return True

        # was: response = self.__select_command()
        response = await self.cp_cmd(
            OP_CODE.OBJECT_SELECT, object_type=OBJ_TYPE.COMMAND
        )
        if len(init_packet) > response["max_size"]:
            raise Exception("Init command is too long")

        if await try_to_recover():
            return

        for r in range(self.RETRIES_NUMBER):
            try:
                # was: self.__create_command(len(init_packet))
                await self.cp_cmd(
                    OP_CODE.OBJECT_CREATE,
                    object_type=OBJ_TYPE.COMMAND,
                    size=len(init_packet),
                )
                await self.__stream_data(data=init_packet)
                # was: self.__execute()
                await self.cp_cmd(OP_CODE.OBJECT_EXECUTE)
            except ValidationException:
                pass
            break
        else:
            raise NordicSemiException("Failed to send init packet")

    async def send_firmware(self, firmware):
        async def try_to_recover():
            if response["offset"] == 0:
                # Nothing to recover
                return

            expected_crc = crc32(firmware[: response["offset"]]) & 0xFFFFFFFF
            remainder = response["offset"] % response["max_size"]

            if expected_crc != response["crc"]:
                # Invalid CRC. Remove corrupted data.
                response["offset"] -= (
                    remainder if remainder != 0 else response["max_size"]
                )
                response["crc"] = (
                    crc32(firmware[: response["offset"]]) & 0xFFFFFFFF
                )
                return

            if (remainder != 0) and (response["offset"] != len(firmware)):
                # Send rest of the page.
                try:
                    to_send = firmware[
                        response["offset"] : response["offset"]
                        + response["max_size"]
                        - remainder
                    ]
                    response["crc"] = await self.__stream_data(
                        data=to_send, crc=response["crc"], offset=response["offset"]
                    )
                    response["offset"] += len(to_send)
                except ValidationException:
                    # Remove corrupted data.
                    response["offset"] -= remainder
                    response["crc"] = (
                        crc32(firmware[: response["offset"]]) & 0xFFFFFFFF
                    )
                    return

            # was: self.__execute()
            await self.cp_cmd(OP_CODE.OBJECT_EXECUTE)
            # was: self._send_event(event_type=DfuEvent.PROGRESS_EVENT, progress=response['offset'])
            logger.info("progress at {}".format(response["offset"]))

        # was: response = self.__select_data()
        response = await self.cp_cmd(OP_CODE.OBJECT_SELECT, object_type=OBJ_TYPE.DATA)
        await try_to_recover()

        for i in range(response["offset"], len(firmware), response["max_size"]):
            data = firmware[i : i + response["max_size"]]
            for r in range(self.RETRIES_NUMBER):
                try:
                    # was: self.__create_data(len(data))
                    await self.cp_cmd(
                        OP_CODE.OBJECT_CREATE, object_type=OBJ_TYPE.DATA, size=len(data)
                    )
                    response["crc"] = await self.__stream_data(
                        data=data, crc=response["crc"], offset=i
                    )
                    # was: self.__execute()
                    await self.cp_cmd(OP_CODE.OBJECT_EXECUTE)
                except ValidationException:
                    pass
                break
            else:
                raise NordicSemiException("Failed to send firmware")
            # was: self._send_event(event_type=DfuEvent.PROGRESS_EVENT, progress=len(data))
            logger.info("progress at {}".format(len(data)))


    async def send_image_package(self, imgpkg):
        """
        @imgpkg a DfuImagePkg instance
        """
        for name, image in imgpkg.images.items():
            start_time = time.time()

            logger.info("Sending init packet for {} ...".format(name))
            with open(image.init_packet, 'rb') as f:
                data    = f.read()
                await self.send_init_packet(data)

            logger.info("Sending firmware bin file for {}...".format(name))
            with open(image.bin_file, 'rb') as f:
                data    = f.read()
                await self.send_firmware(data)

            end_time = time.time()
            delta_time = end_time - start_time
            logger.info("Image sent for {} in {0}s".format(name, delta_time))

async def scan_dfu_devices(timeout=10, **kwargs):
    devices = []
    candidates = await discover(timeout=timeout)
    for d in candidates:
        match = None
        if "uuids" in d.metadata:
            advertised = d.metadata["uuids"]  # service uuids
            # logger.debug(str(BLE_UUID.S_NORDIC_SEMICONDUCTOR_ASA) + " in " + str(advertised))
            if BLE_UUID.S_NORDIC_SEMICONDUCTOR_ASA in advertised:
                match = "nordic semi asa"
            elif BLE_UUID.C_DFU_BUTTONLESS_BONDED in advertised:
                match = "DFU bonded"
            elif BLE_UUID.C_DFU_BUTTONLESS_UNBONDED in advertised:
                match = "DFU unbonded"

        if match:
            logger.info(
                "dfu device: {}  rssi:{} dBm  name:{} ({})".format(
                    d.address, d.rssi, d.name, match
                )
            )
            devices.append(d)
        else:
            logger.debug("ignoring device={}".format(d))

    return devices

