import client from './client';

export const facultyApi = {
  getFacultyList: (params = {}) => client.get('/faculty/', { params }),
  getFacultyProfile: (id) => client.get(`/faculty/${id}/`),
  getMyProfile: () => client.get('/faculty/me/'),
  updateMyProfile: (data) => client.patch('/faculty/me/update/', data),
  uploadMyDocument: (docType, file) => {
    const form = new FormData();
    form.append('document_type', docType);
    form.append('file', file);
    return client.post('/faculty/me/documents/upload/', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  downloadMyDocument: (docId) => client.get(`/faculty/me/documents/${docId}/download/`, { responseType: 'blob' }),
  revealMyDocument: (docId, reason) => client.post(`/faculty/me/documents/${docId}/reveal/`, { reason }),
  revealSensitive: (id, reason) => client.post(`/faculty/${id}/reveal/`, { reason }),
  createFaculty: (data) => client.post('/faculty/', data),
  getAssignments: (params = {}) => client.get('/faculty/assignments/', { params }),
  createAssignment: (data) => client.post('/faculty/assignments/', data),
  deactivateAssignment: (id, reason) => client.post(`/faculty/assignments/${id}/deactivate/`, { reason }),
};

export default facultyApi;
