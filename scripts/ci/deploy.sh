#!/bin/bash

set -e
export TRAVIS_TAG=v0.8.16

METADATA_VERSION=v$(grep -Po "(?<=^version=).*" qfieldsync/metadata.txt)

if [ "$METADATA_VERSION" != "${TRAVIS_TAG}" ]; then
  echo -e "\e[31mVersion tag in metadata ($METADATA_VERSION) and in git tag ($TRAVIS_TAG) do not match.\e[0m"
  echo -e "\e[31mThis will not be deployed.\e[0m"
  exit -1
fi

pushd qfieldsync
make package VERSION=${TRAVIS_TAG}
popd

echo "./scripts/plugin_upload.py -u ${OSGEO_USERNAME} -w ${OSGEO_PASSWORD} qfieldsync/qfieldsync.zip"
