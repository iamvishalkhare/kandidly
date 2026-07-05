# Web SPA dev image (Vite). Prod build served statically is out of v1 dev scope.
FROM docker.io/library/node:22-slim

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
