#!/bin/bash

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🚀 Запуск локальной разработки в Docker...${NC}"

# Остановка контейнеров если они запущены
echo -e "${YELLOW}📥 Останавливаем контейнеры...${NC}"
docker-compose -f docker-compose.local.yml down

# Очистка Docker
echo -e "${YELLOW}🧹 Очищаем Docker...${NC}"
docker system prune -f --volumes

# Сборка и запуск контейнеров
echo -e "${YELLOW}🏗️  Собираем и запускаем контейнеры...${NC}"
docker-compose -f docker-compose.local.yml up --build

# Обработка сигнала прерывания (Ctrl+C)
trap 'echo -e "${RED}👋 Останавливаем контейнеры...${NC}" && docker-compose -f docker-compose.local.yml down' INT