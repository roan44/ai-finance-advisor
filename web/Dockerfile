FROM node:20
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
EXPOSE 3000
CMD ["npm","run","dev","--","-p","3000","-H","0.0.0.0"]
