# Use the official Node.js 20 Alpine image
FROM node:20-alpine

# Set working directory inside the container
WORKDIR /app

# Copy package files first (Docker caches this layer)
COPY package*.json ./

RUN npm install --production

# Copy the rest of your application code
COPY . .

# Tell Docker your app uses port 3000
EXPOSE 3000

# Command to start the app inside the container
CMD ["node", "server.js"]