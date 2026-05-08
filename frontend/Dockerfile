FROM node:22-alpine

WORKDIR /app
COPY frontend/package.json /app/package.json
COPY frontend/package-lock.json /app/package-lock.json
RUN npm ci

COPY frontend /app

EXPOSE 3000
CMD ["npm", "run", "dev"]
