__DIR="$(cd "$(dirname "${BASH_SOURCE:-$0}")" && pwd)"

python3 $__DIR/cli.py $@

__CD_FILE=__cd
if [ -f $__CD_FILE ]; then
    __CD_PATH=$(cat $__CD_FILE)
    rm -f $__CD_FILE
    cd $__CD_PATH
    unset __CD_PATH
fi
unset __CD_FILE

__RM_FILE=__rm
if [ -f $__RM_FILE ]; then
    __RM_PATH=$(cat $__RM_FILE)
    rm -f $__RM_FILE
    rm -rf $__RM_PATH
    unset __RM_PATH
fi
unset __RM_FILE

unset __DIR
unset __EXIT_CODE
