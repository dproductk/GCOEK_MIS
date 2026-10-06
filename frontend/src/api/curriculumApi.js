import client from './client';

export const curriculumApi = {
  getSubjects: (params = {}) => client.get('/curriculum/subjects/', { params }),
  createSubject: (data) => client.post('/curriculum/subjects/', data),
  deleteSubject: (id) => client.delete(`/curriculum/subjects/${id}/`),
  getSchemes: (params = {}) => client.get('/curriculum/schemes/', { params }),
  createScheme: (data) => client.post('/curriculum/schemes/', data),
  deleteScheme: (id) => client.delete(`/curriculum/schemes/${id}/`),
  publishScheme: (id) => client.post(`/curriculum/schemes/${id}/publish/`),
  retireScheme: (id) => client.post(`/curriculum/schemes/${id}/retire/`),
  getSchemeSubjects: (params = {}) => client.get('/curriculum/scheme-subjects/', { params }),
  getMySubjects: (semester) => client.get('/curriculum/scheme-subjects/my-subjects/', { params: { semester } }),
  createSchemeSubject: (data) => client.post('/curriculum/scheme-subjects/', data),
  deleteSchemeSubject: (id) => client.delete(`/curriculum/scheme-subjects/${id}/`),
  createAssessmentComponent: (data) => client.post('/curriculum/assessment-components/', data),
  deleteAssessmentComponent: (id) => client.delete(`/curriculum/assessment-components/${id}/`),
  getElectiveGroups: (params = {}) => client.get('/curriculum/elective-groups/', { params }),
  createElectiveGroup: (data) => client.post('/curriculum/elective-groups/', data),
};

export default curriculumApi;
