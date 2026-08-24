#!/bin/bash
docker stop calculadora-container 2>/dev/null && echo "Calculadora parada." || echo "Já estava parada."
