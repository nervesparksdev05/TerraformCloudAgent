import axios from 'axios';
import { signInWithPopup } from 'firebase/auth';
import { auth, googleProvider } from './firebase';

const FIREBASE_API_KEY = "AIzaSyCW33xFHeQOjnc831Sqae0b1_-2rtpDAaY";
const BASE_URL = "https://identitytoolkit.googleapis.com/v1/accounts";

const authClient = axios.create({
    baseURL: BASE_URL,
});

export const authService = {
    signIn: async (email, password) => {
        const { data } = await authClient.post(`:signInWithPassword?key=${FIREBASE_API_KEY}`, {
            email,
            password,
            returnSecureToken: true
        });
        return data;
    },

    signUp: async (email, password) => {
        const { data } = await authClient.post(`:signUp?key=${FIREBASE_API_KEY}`, {
            email,
            password,
            returnSecureToken: true
        });
        return data;
    },

    signInWithGoogle: async () => {
        const result = await signInWithPopup(auth, googleProvider);
        const user = result.user;
        const idToken = await user.getIdToken();
        return {
            idToken,
            refreshToken: user.refreshToken,
            email: user.email,
            localId: user.uid,
            expiresIn: '3600'
        };
    },

    refreshToken: async (refreshToken) => {
        const { data } = await axios.post(`https://securetoken.googleapis.com/v1/token?key=${FIREBASE_API_KEY}`, {
            grant_type: "refresh_token",
            refresh_token: refreshToken
        });
        return {
            idToken: data.id_token,
            refreshToken: data.refresh_token,
            expiresIn: data.expires_in
        };
    },

    sendPasswordReset: async (email) => {
        await authClient.post(`:sendOobCode?key=${FIREBASE_API_KEY}`, {
            requestType: "PASSWORD_RESET",
            email
        });
    }
};

export default authService;
