FROM node:22-alpine
ENV NODE_ENV=production
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY app.js server.js ./
COPY controller ./controller
COPY model ./model
COPY routes ./routes
COPY utils ./utils

EXPOSE 3002
CMD ["npm", "start"]

