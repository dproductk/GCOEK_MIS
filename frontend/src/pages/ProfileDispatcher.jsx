import { useAuth } from '../context/AuthContext';
import StudentProfilePage from './student/StudentProfilePage';
import FacultyProfilePage from './faculty/FacultyProfilePage';

export default function ProfileDispatcher() {
  const { user, activeRole } = useAuth();

  if (activeRole?.codename === 'STUDENT' || user?.user_type === 'STUDENT') {
    return <StudentProfilePage />;
  }

  return <FacultyProfilePage />;
}
