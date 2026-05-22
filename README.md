# RiceMesh GIS Processing
This is a GIS Processing module for RiceMesh project.

## Requirements
- Python >= 3.12
- uv

## Installation
- Clone this repo
- Clone WebODM official repo
- Run WebODM using their run script

## Running
Run this scripts in the following order:
1. ```bash
   docker compose --profile dev up
   ```
2. ```bash
   bash 1-server-run.bash
   ```
3. ```bash
   bash 2-arq-worker.bash
   ```
