'use client';

import { useAuth } from '@/contexts/AuthContext';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { TrendingUp, LayoutDashboard, Settings, LogOut } from 'lucide-react';

const NAV_LINKS = [
    { href: '/portfolios', label: 'Portfolios', icon: LayoutDashboard },
    { href: '/admin',      label: 'Admin',      icon: Settings },
];

export const Navbar = () => {
    const { logout, user } = useAuth();
    const pathname = usePathname();

    return (
        <nav className="bg-white border-b shadow-sm">
            <div className="max-w-7xl mx-auto px-6">
                <div className="flex items-center justify-between h-14">
                    {/* Brand */}
                    <Link href="/portfolios" className="flex items-center gap-2 font-semibold text-gray-900 hover:text-indigo-600 transition-colors">
                        <TrendingUp className="w-5 h-5 text-indigo-600" />
                        <span>Virtual Hedge Fund</span>
                    </Link>

                    {/* Nav links */}
                    <div className="flex items-center gap-1">
                        {NAV_LINKS.map(({ href, label, icon: Icon }) => {
                            const active = pathname === href || pathname.startsWith(href + '/');
                            return (
                                <Link
                                    key={href}
                                    href={href}
                                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                                        active
                                            ? 'bg-indigo-50 text-indigo-700'
                                            : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                                    }`}
                                >
                                    <Icon className="w-3.5 h-3.5" />
                                    {label}
                                </Link>
                            );
                        })}
                    </div>

                    {/* User + logout */}
                    <div className="flex items-center gap-3">
                        <span className="text-xs text-gray-400 hidden sm:block">{user?.email}</span>
                        <button
                            onClick={logout}
                            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 rounded-md hover:bg-red-50 hover:text-red-600 transition-colors"
                        >
                            <LogOut className="w-3.5 h-3.5" />
                            Logout
                        </button>
                    </div>
                </div>
            </div>
        </nav>
    );
};
