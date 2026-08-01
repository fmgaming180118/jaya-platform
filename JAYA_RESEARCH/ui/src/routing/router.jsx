import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useState,
} from 'react';

import { normalizeInternalTarget } from './contracts.js';

const RouterContext = createContext(null);

export function BrowserRouter({ children }) {
    const [pathname, setPathname] = useState(() => window.location.pathname);

    useEffect(() => {
        const handlePopState = () => setPathname(window.location.pathname);
        window.addEventListener('popstate', handlePopState);
        return () => window.removeEventListener('popstate', handlePopState);
    }, []);

    const navigate = useCallback((target, options = {}) => {
        const href = normalizeInternalTarget(target, window.location.origin);
        if (options.replace) {
            window.history.replaceState(null, '', href);
        } else {
            window.history.pushState(null, '', href);
        }
        setPathname(window.location.pathname);
    }, []);

    const value = useMemo(() => ({ navigate, pathname }), [navigate, pathname]);
    return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

const useRouter = () => {
    const value = useContext(RouterContext);
    if (!value) throw new Error('Router hooks must be used inside BrowserRouter');
    return value;
};

export const useNavigate = () => useRouter().navigate;
export const usePathname = () => useRouter().pathname;

export function Link({ children, className, onClick, target, to, ...props }) {
    const { navigate } = useRouter();
    const href = normalizeInternalTarget(to, window.location.origin);
    const handleClick = (event) => {
        onClick?.(event);
        if (
            event.defaultPrevented
            || event.button !== 0
            || event.metaKey
            || event.ctrlKey
            || event.shiftKey
            || event.altKey
            || (target && target !== '_self')
        ) {
            return;
        }
        event.preventDefault();
        navigate(href);
    };

    return (
        <a {...props} className={className} href={href} onClick={handleClick} target={target}>
            {children}
        </a>
    );
}

export function NavLink({ children, className, to, ...props }) {
    const pathname = usePathname();
    const href = normalizeInternalTarget(to, window.location.origin);
    const targetPath = new URL(href, window.location.origin).pathname;
    const isActive = pathname === targetPath;
    const resolvedClassName = typeof className === 'function'
        ? className({ isActive })
        : className;
    const resolvedChildren = typeof children === 'function'
        ? children({ isActive })
        : children;
    return (
        <Link {...props} className={resolvedClassName} to={href}>
            {resolvedChildren}
        </Link>
    );
}
