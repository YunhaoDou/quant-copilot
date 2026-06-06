FROM node:20-alpine

WORKDIR /app

COPY package.json pnpm-lock.yaml* package-lock.json* ./
RUN if [ -f pnpm-lock.yaml ]; then \
        npm install -g pnpm && pnpm install; \
    else \
        npm install; \
    fi

COPY . .

EXPOSE 3000
CMD ["npm", "run", "dev"]
