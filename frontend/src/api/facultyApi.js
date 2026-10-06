import client from './client';

export const facultyApi = {
  getFacultyList: (params = {}) => client.get('/faculty/', { params }),
  getFacultyProfile: (id) => client.get(`/faculty/${id}/`),
  getMyProfile: () => client.get('/faculty/me/'),
  revealSensitive: (id, reason) => client.post(`/faculty/${id}/reveal/`, { reason }),
  createFaculty: (data) => client.post('/faculty/', data),
  getAssignments: (params = {}) => client.get('/faculty/assignments/', { params }),
  createAssignment: (data) => client.post('/faculty/assignments/', data),
  deactivateAssignment: (id, reason) => client.post(`/faculty/assignments/${id}/deactivate/`, { reason }),
};

export default facultyApi;
