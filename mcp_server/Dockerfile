FROM hashicorp/terraform-mcp-server:latest AS mcp-bin

FROM node:20-slim

COPY --from=mcp-bin /bin/terraform-mcp-server /usr/local/bin/terraform-mcp-server

RUN npm install -g mcp-proxy

ENV PORT=8080
EXPOSE 8080

CMD ["mcp-proxy", "--streamEndpoint", "/sse", "--", "terraform-mcp-server", "stdio", "--toolsets=registry"]
