'use client';

import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { CheckCircle, XCircle, AlertCircle, X } from 'lucide-react';

type ToastType = 'success' | 'error' | 'info';

interface Toast {
    id: number;
    type: ToastType;
    message: string;
}

interface ToastContextValue {
    success: (message: string) => void;
    error: (message: string) => void;
    info: (message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let nextId = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
    const [toasts, setToasts] = useState<Toast[]>([]);

    const add = useCallback((type: ToastType, message: string) => {
        const id = ++nextId;
        setToasts(prev => [...prev, { id, type, message }]);
        setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 4000);
    }, []);

    const remove = (id: number) => setToasts(prev => prev.filter(t => t.id !== id));

    const value: ToastContextValue = {
        success: (msg) => add('success', msg),
        error:   (msg) => add('error', msg),
        info:    (msg) => add('info', msg),
    };

    return (
        <ToastContext.Provider value={value}>
            {children}
            <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
                {toasts.map(toast => (
                    <ToastItem key={toast.id} toast={toast} onDismiss={() => remove(toast.id)} />
                ))}
            </div>
        </ToastContext.Provider>
    );
}

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
    const [visible, setVisible] = useState(false);

    useEffect(() => {
        requestAnimationFrame(() => setVisible(true));
    }, []);

    const styles: Record<ToastType, { bg: string; icon: React.ReactNode }> = {
        success: { bg: 'bg-green-50 border-green-200 text-green-800', icon: <CheckCircle className="w-4 h-4 text-green-500 shrink-0" /> },
        error:   { bg: 'bg-red-50 border-red-200 text-red-800',       icon: <XCircle className="w-4 h-4 text-red-500 shrink-0" /> },
        info:    { bg: 'bg-blue-50 border-blue-200 text-blue-800',     icon: <AlertCircle className="w-4 h-4 text-blue-500 shrink-0" /> },
    };

    const { bg, icon } = styles[toast.type];

    return (
        <div
            className={`pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-lg border shadow-md text-sm max-w-sm transition-all duration-300 ${bg} ${
                visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'
            }`}
        >
            {icon}
            <span className="flex-1">{toast.message}</span>
            <button onClick={onDismiss} className="ml-1 opacity-50 hover:opacity-100">
                <X className="w-3.5 h-3.5" />
            </button>
        </div>
    );
}

export function useToast(): ToastContextValue {
    const ctx = useContext(ToastContext);
    if (!ctx) throw new Error('useToast must be used within ToastProvider');
    return ctx;
}
