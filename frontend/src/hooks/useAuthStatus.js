import { useState, useEffect } from 'react';
import { getFreshAuthStatus, subscribeAuth } from '../utils/authSession';

// Реактивная подписка на общий auth-стор: seed из кэша (getFreshAuthStatus) +
// обновление через subscribeAuth. Заменяет копипасту
// `useState(getFreshAuthStatus) + useEffect(() => subscribeAuth(setAuth), [])`,
// которая раньше жила в Sidebar / UserMenu / ProfilePage / SiteOrdersPage.
export const useAuthStatus = () => {
    const [auth, setAuth] = useState(getFreshAuthStatus);
    useEffect(() => subscribeAuth(setAuth), []);
    return auth;
};

// Сахар для частого случая «показывать ли супер-функцию».
export const useSuperuser = () => useAuthStatus().isSuperuser === true;
