__DIR="$(cd "$(dirname "${BASH_SOURCE:-$0}")" && pwd)"

__COMMAND=t
alias $__COMMAND="source $__DIR/cli.sh"
echo "[competition-tools] Alias '$__COMMAND' has been set."
unset __COMMAND

unset __DIR
