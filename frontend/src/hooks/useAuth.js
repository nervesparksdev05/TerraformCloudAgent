import { useState, useEffect } from 'react';

export const useAuth = () => {
    const [authUser, setAuthUser] = useState(null);

    useEffect(() => {
        const storedAuth = localStorage.getItem('tca_auth');
        if (storedAuth) {
            try {
                const data = JSON.parse(storedAuth);
                if (data.expiry > Date.now()) {
                    setAuthUser(data);
                } else {
                    localStorage.removeItem('tca_auth');
                }
            } catch (e) {
                localStorage.removeItem('tca_auth');
            }
        }
    }, []);

    const logout = () => {
        localStorage.removeItem('tca_auth');
        setAuthUser(null);
    };

    return { authUser, setAuthUser, logout };
};

export default useAuth;
