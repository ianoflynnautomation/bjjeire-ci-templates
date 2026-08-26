import http from 'k6/http';
import { check, sleep } from 'k6';

const API_URL = (__ENV.API_URL || 'http://127.0.0.1:8080').replace(/\/$/, '');

export const options = {
  vus: 5,
  duration: '20s',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<800'],
  },
};

const PATHS = ['/actuator/health', '/api/v1/gym?page=1&pageSize=10', '/api/v1/bjjevent?page=1&pageSize=10'];

export default function catalogSmoke() {
  for (const path of PATHS) {
    const response = http.get(`${API_URL}${path}`);
    check(response, {
      'status is 2xx': (res) => res.status >= 200 && res.status < 300,
    });
  }
  sleep(1);
}
