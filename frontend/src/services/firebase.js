import { initializeApp } from 'firebase/app';
import { getAuth, GoogleAuthProvider } from 'firebase/auth';

const firebaseConfig = {
    apiKey: "AIzaSyCW33xFHeQOjnc831Sqae0b1_-2rtpDAaY",
    authDomain: "terraformcloudagent-7cfb6.firebaseapp.com",
    projectId: "terraformcloudagent-7cfb6",
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const googleProvider = new GoogleAuthProvider();
