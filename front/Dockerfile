FROM node:20-slim

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Next bakes the /api/* proxy target into the build: pass the back's URL here.
ARG API_URL=http://localhost:8000
ARG NEXT_PUBLIC_CALENDLY_URL=https://calendly.com/
ENV API_URL=$API_URL NEXT_PUBLIC_CALENDLY_URL=$NEXT_PUBLIC_CALENDLY_URL
RUN npm run build && npm prune --omit=dev

ENV NODE_ENV=production PORT=3000
EXPOSE 3000
CMD ["npm", "start"]
