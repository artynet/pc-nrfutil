
import sys
import asyncio
import logging

from nordicsemi.dfu.dfu_transport_bleak import DfuDevice, DfuImagePkg


logger = logging.getLogger(__name__)

async def run():
    address = sys.argv[1]
    zipfile = sys.argv[2]
    imgpkg = DfuImagePkg(zipfile)
    async with DfuDevice(address=address) as dev:
        await dev.send_image_package(imgpkg)



def set_verbose(verbose_level):
    loggers = [logging.getLogger("nordicsemi"), logger]
    #for name in logging.root.manager.loggerDict:
    #    print(name) #loggers = [logging.getLogger(name) 
        

    if verbose_level <= 0:
        level = logging.WARNING
    elif verbose_level == 2:
        level = logging.INFO
    elif verbose_level >= 3:
        level = logging.DEBUG

    if verbose_level >= 4:
        bleak_logger = logging.getLogger("bleak")
        loggers.append(bleak_logger)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)

    formatter = logging.Formatter("%(levelname)s:%(name)s:%(lineno)d: %(message)s")
    handler.setFormatter(formatter)

    for l in loggers:
        l.setLevel(level)
        l.addHandler(handler)


def main():
    set_verbose(3)
    logger.debug("Starting")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())

if __name__ == "__main__":
    main()

