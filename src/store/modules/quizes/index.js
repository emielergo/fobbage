import actions from './actions';
import mutations from './mutations';
import getters from './getters';

export default {
  state: {
    loading: false,
    quizes: [],
    sessions: [],
    activeSessionId: null,
    error: '',
    bluff: undefined,
    guess: undefined,
    activeQuestion: undefined,
  },
  mutations,
  getters,
  actions,
};
