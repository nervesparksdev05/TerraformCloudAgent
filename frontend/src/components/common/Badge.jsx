import React from 'react';

export const Badge = ({ children, variant = 'default', className = '' }) => {
  const variants = {
    default: 'bg-gray-500/10 text-gray-400',
    success: 'bg-green-500/10 text-green-500',
    error: 'bg-red-500/10 text-red-500',
    warning: 'bg-yellow-500/10 text-yellow-500',
    info: 'bg-blue-500/10 text-blue-500',
  };

  return (
    <span className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium uppercase tracking-widest ${variants[variant]} ${className}`}>
      {children}
    </span>
  );
};

export default Badge;
