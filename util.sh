#!/bin/bash

set -eo pipefail

make_tar() {
  echo "Tarring the ball..."
  pushd .. && tar -cvf phcode42v2/phcode42v2.tgz -X phcode42v2/exclude_files.txt phcode42v2/* && popd
}

clean() {
  rm -f phcode42v2.tgz
}

deploy() {
  echo "Moving to remote..."
  sshpass -p "${PHANTOM_VM_PASSWORD}" scp phcode42v2.tgz "phantom@${PHANTOM_VM_IP_ADDR}":/home/phantom
  echo "Untarring on remote..."
  sshpass -p "${PHANTOM_VM_PASSWORD}" ssh phantom@${PHANTOM_VM_IP_ADDR} \
		"rm -rf phcode42v2 && tar -xvf phcode42v2.tgz && cd phcode42v2 && phenv python /opt/phantom/bin/compile_app.pyc -i"
}

print_usage() {
  echo "./util.sh <tar, clean, deploy, ssh, open-web>"
}

main() {
  case $1 in
  "")
    echo "Kindly supply a command" && print_usage && exit 0
    ;;
  tar)
    clean
    make_tar
    ;;
  clean)
    clean
    ;;
  deploy)
    make_tar
    deploy
    ;;
  ssh)
    sshpass -p "${PHANTOM_VM_PASSWORD}" ssh phantom@${PHANTOM_VM_IP_ADDR}
    ;;
  open-web)
    open https://${PHANTOM_VM_IP_ADDR}:9999
    ;;
  *)
    echo "Not a valid command" && print_usage && exit 0
  esac
}

main "$@"
