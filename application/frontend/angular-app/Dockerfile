# -------- BUILD STAGE --------
FROM node:20 AS builder

WORKDIR /app

COPY package*.json ./
RUN npm install

RUN npm install rxjs@7.8.2 --save --legacy-peer-deps

COPY . .

RUN npm run build

# -------- NGINX STAGE --------
FROM nginx:1.25-alpine

RUN rm /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist/angular-app/browser /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]