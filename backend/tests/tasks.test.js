const request = require('supertest');
const app = require('../server');

describe('TaskFlow API', () => {

  test('GET /api/health returns ok', async () => {
    const res = await request(app).get('/api/health');
    expect(res.statusCode).toBe(200);
    expect(res.body.status).toBe('ok');
    expect(res.body.service).toBe('taskflow-api');
  });

  test('GET /api/tasks returns array', async () => {
    const res = await request(app).get('/api/tasks');
    expect(res.statusCode).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
  });

  test('POST /api/tasks creates a task', async () => {
    const res = await request(app)
      .post('/api/tasks')
      .send({ title: 'Test task from Jest', priority: 'medium' });
    expect(res.statusCode).toBe(201);
    expect(res.body.title).toBe('Test task from Jest');
    expect(res.body.id).toBeDefined();
  });

  test('POST /api/tasks fails without title', async () => {
    const res = await request(app)
      .post('/api/tasks')
      .send({ priority: 'high' });
    expect(res.statusCode).toBe(400);
    expect(res.body.error).toBe('title is required');
  });

  test('DELETE /api/tasks/:id deletes a task', async () => {
    const create = await request(app)
      .post('/api/tasks')
      .send({ title: 'Task to delete', priority: 'low' });
    const id = create.body.id;
    const res = await request(app).delete(`/api/tasks/${id}`);
    expect(res.statusCode).toBe(200);
    expect(res.body.message).toBe('Task deleted');
  });

});