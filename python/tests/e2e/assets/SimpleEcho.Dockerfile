FROM nginx:latest
ARG SECRET=NotASecret
ENV SECRET ${SECRET}
CMD echo $SECRET
