import '@testing-library/jest-dom';

// Mock scrollIntoView which is not available in jsdom
Element.prototype.scrollIntoView = () => {};
