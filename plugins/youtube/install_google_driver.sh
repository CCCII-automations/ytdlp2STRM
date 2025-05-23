#!/bin/bash

set -e

# Detect Chrome full version
FULL_VERSION=$(google-chrome --version | grep -oP "\d+\.\d+\.\d+\.\d+")
MAJOR_VERSION=$(echo "$FULL_VERSION" | cut -d '.' -f 1)

# Get latest driver version for the MAJOR version (safe fallback)
DRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$MAJOR_VERSION")

if [[ "$DRIVER_VERSION" == *"Error"* || -z "$DRIVER_VERSION" ]]; then
    echo "❌ Could not resolve a compatible ChromeDriver version for Chrome $MAJOR_VERSION"
    exit 1
fi

echo "Detected Chrome version: $FULL_VERSION"
echo "Installing ChromeDriver version: $DRIVER_VERSION"

# Download and install
wget -q "https://chromedriver.storage.googleapis.com/${DRIVER_VERSION}/chromedriver_linux64.zip"
unzip -o chromedriver_linux64.zip
chmod +x chromedriver
sudo mv -f chromedriver /usr/local/bin/
rm chromedriver_linux64.zip

echo "✅ ChromeDriver $DRIVER_VERSION installed at /usr/local/bin/chromedriver"

