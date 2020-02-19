
# `realpath` and `readlink -f` not on MacOS :(
_realpath()
{
    python3 -c "import os; print(os.path.realpath('$1'))"
}

# Absolute path to this script
SCRIPT=$(_realpath "$0")
# Absolute path this script is in
SCRIPTPATH=$(dirname "$SCRIPT")

PYTHONPATH="$SCRIPTPATH:$PYTHONPATH" 

# test with your dirty branch of "bleak" (Bluetooth LE lib)
if [ -n "$BLEAK" ]; then
    BLEAK=$(_realpath "$BLEAK")
    #echo "BLEAK $BLEAK"
    PYTHONPATH="$BLEAK:$PYTHONPATH" 
fi


APP_ADDR="F2:1F:2B:52:48:9E" 
DFU_ADDR="F2:1F:2B:52:48:9F" 

BBLOG="$HOME/ws/lohmega/jamble/bblog.sh"
sh $BBLOG device-info -a $APP_ADDR -vvv

echo "Enter DFU..."
sh $BBLOG dfu -a $APP_ADDR -vvv

echo "PYTHONPATH: $PYTHONPATH" 1>&2

#DFU_ZIP_PKG=$HOME/Documents/bb_v10_logger_dfu_v0_1_26.zip
DFU_ZIP_PKG=$HOME/Documents/bb_v10_logger_dfu_v0_1_29.zip

CLI_SCRIPT="$SCRIPTPATH/nordicsemi/bleak_dfu_cli.py"
PYTHONPATH="$PYTHONPATH" python3 $CLI_SCRIPT $DFU_ADDR  $DFU_ZIP_PKG


sh $BBLOG device-info -a $APP_ADDR -vvv
