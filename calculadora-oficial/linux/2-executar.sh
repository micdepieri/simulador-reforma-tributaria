#!/bin/bash
docker run -t -i --rm -p 8080:8080 -p 8081:8081 -p 80:80 -w /calculadora --name calculadora-container calculadora-image bash start.sh