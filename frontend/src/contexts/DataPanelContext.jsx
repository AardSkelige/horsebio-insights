/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useState } from 'react';
import PropTypes from 'prop-types';

const DataPanelContext = createContext();

export const DataPanelProvider = ({ children }) => {
    const [open, setOpen] = useState(false);
    const toggle = () => setOpen(v => !v);
    const close = () => setOpen(false);
    return (
        <DataPanelContext.Provider value={{ open, toggle, close }}>
            {children}
        </DataPanelContext.Provider>
    );
};
DataPanelProvider.propTypes = { children: PropTypes.node.isRequired };

export const useDataPanel = () => useContext(DataPanelContext);
