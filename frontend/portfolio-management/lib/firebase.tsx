import { initializeApp } from 'firebase/app';
import { getAuth } from 'firebase/auth';

const firebaseConfig = {
    apiKey: "AIzaSyDE8rVE0f-ub7Vz3umE6s3bWkkeIVdzv_Q",
    authDomain: "virtual-hedge-fund-e92de.firebaseapp.com",
    projectId: "virtual-hedge-fund-e92de",
    storageBucket: "virtual-hedge-fund-e92de.firebasestorage.app",
    messagingSenderId: "826217246802",
    appId: "1:826217246802:web:7549a96555a0f594896f8b"
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export { GoogleAuthProvider, signInWithPopup } from 'firebase/auth';


